import libsonata as lb
import numpy as np
import h5py
import pandas as pd
import sys
from mpi4py import MPI
from scipy.spatial import distance
from scipy.spatial.transform import Rotation
import json
from scipy.interpolate import RegularGridInterpolator

def add_data(h5, gid, coeffs ,population_name):

    dset = 'electrodes/'+population_name+'/scaling_factors'

    node_ids = h5[population_name+'/node_ids'][:]

    gidIndex = np.where(gid==node_ids)[0][0]


    offset0 = h5[population_name+'/offsets'][gidIndex] # Finds offset in  'electrodes/'+population_name+'/scaling_factors' for this particular node id


    if gidIndex == len(h5[population_name+'/offsets'][:])-1: # If this is the last node in the list, we write the coefficients up to the end of the coefficient array

        h5[dset][offset0:] = coeffs

    else: # Otherwise, we write up to the offset for the next node
        offset1 = h5[population_name+'/offsets'][gidIndex+1]
        h5[dset][offset0:offset1] = coeffs

def get_line_coeffs(startPos,endPos,electrodePos,sigma):

    '''
    startPos and endPos are the starting and ending positions of the segment
    sigma is the extracellular conductivity
    '''

    segLength = np.linalg.norm(startPos-endPos)

    x1 = electrodePos[0]-endPos[0]
    y1 = electrodePos[1]-endPos[1]
    z1 = electrodePos[2]-endPos[2]

    xdiff = endPos[0]-startPos[0]
    ydiff = endPos[1]-startPos[1]
    zdiff = endPos[2]-startPos[2]

    h = 1/segLength * (x1*xdiff + y1*ydiff + z1*zdiff)

    r2 = (electrodePos[0]-startPos[0])**2 + (electrodePos[1]-startPos[1])**2 + (electrodePos[2]-startPos[2])**2 - h**2
    r2 = np.abs(r2)
    l = h + segLength

    segCoeff = 1/(4*np.pi*sigma*segLength)*np.log(np.abs(((h**2+r2)**.5-h)/((l**2+r2)**.5-l)))

    return segCoeff

def get_coeffs_lfp(positions,columns,electrodePos,sigma):

    for i in range(len(positions.columns)-1):

        if positions.columns[i][-1]==0: # Implies that it is a soma

            somaPos = positions.iloc[:,i]

            distance = np.linalg.norm(somaPos-electrodePos)

            somaCoeff = 1/(4*np.pi*sigma*distance) # We treat the soma as a point, so the contribution at the electrode follows the formula for the potential from a point source

            if i == 0:
                coeffs = somaCoeff
            else:

                coeffs = np.hstack((coeffs,somaCoeff))

        elif positions.columns[i][-1]==positions.columns[i+1][-1]: # Ensures we are not at the far end of a section

            segCoeff = get_line_coeffs(startPos,endPos,electrodePos,sigma)

            coeffs = np.hstack((coeffs,segCoeff))


    coeffs = pd.DataFrame(data=coeffs[np.newaxis,:])

    coeffs.columns = columns

    return coeffs

def geth5Dataset(h5f, group_name, dataset_name):
    """
    Find and get dataset from h5 file.
    out = geth5Dataset(h5f, group_name, dataset_name)
    h5f - string - h5 file path and name
    group_name - string - where to initiate search, '/' for root
    dataset_name - string - dataset to be found
    return - numpy array
    """

    def find_dataset(name):
        """ Find first object with dataset_name anywhere in the name """
        if dataset_name in name:
            return name

    with h5py.File(h5f, 'r') as f:
        k = f[group_name].visit(find_dataset)
        return f[group_name + '/' + k][()]

def get_coeffs_eeg(positions, path_to_fields):

    '''
    path_to_fields is the path to the h5 file containing the potential field, outputted from Sim4Life
    path_to_positions is the path to the output from the position-finding script
    '''

    # Get new output file potential field

    with h5py.File(path_to_fields, 'r') as f:
        for i in f['FieldGroups']:
            tmp = 'FieldGroups/' + i + '/AllFields/EM Potential(x,y,z,f0)/_Object/Snapshots/0/'
        pot = geth5Dataset(path_to_fields, tmp, 'comp0')
        for i in f['Meshes']:
            tmp = 'Meshes/'+i
            break
        x = geth5Dataset(path_to_fields, tmp, 'axis_x')
        y = geth5Dataset(path_to_fields, tmp, 'axis_y')
        z = geth5Dataset(path_to_fields, tmp, 'axis_z')


        try:
            currentApplied = f['CurrentApplied'][0] # The potential field should have a current, but if not, just assume it is 1
        except:
            currentApplied = 1


    positions *= 1e-6 # Converts um to m, to match the potential field file

    xSelect = positions.values[0]
    ySelect = positions.values[1]
    zSelect = positions.values[2]


    selections = np.array([xSelect, ySelect, zSelect]).T


    InterpFcn = RegularGridInterpolator((x, y, z), pot[:, :, :, 0], method='linear')

    out2rat = InterpFcn(selections) # Interpolate potential field at location of neural segments


    outdf = pd.DataFrame(data=(out2rat / currentApplied), columns=positions.columns) # Scale potential field by applied current

    return outdf

def load_positions(segment_position_folder, filesPerFolder, numPositionFiles, rank, nranks):

    '''
    Loads positions file based on rank
    '''

    index = int(rank % numPositionFiles) # Selects position file to load
    folder = int(index/filesPerFolder) # Finds which subfolder the position file is in

    allPositions = pd.read_pickle(segment_position_folder+'/'+str(folder)+'/positions'+str(index)+'.pkl')

    return allPositions

def getSegmentMidpts(positions,node_ids):

    for gidx, gid in enumerate(node_ids):

        position = positions[gid]

        secIds = np.array(list(position.columns))
        uniqueSecIds = np.unique(secIds)

        for sId in uniqueSecIds: # Iterates through sections

            pos = position.iloc[:,np.where(sId == secIds)[0]]

            if sId == 0: # Implies that section is a soma, so we just take the position from the file

                newcols = pd.MultiIndex.from_product([[gid],pos.columns])
                pos.columns = newcols

                if gidx == 0:
                    newPos = pos
                else:
                    newPos = pd.concat((newPos,pos),axis=1)

            elif np.shape(pos.values)[-1] == 1: # If there is only one point in the section, we just take the value
                newcols = pd.MultiIndex.from_product([[gid],pos.columns])
                pos.columns = newcols
                newPos = pd.concat((newPos,pos),axis=1)

            else: # We take the midpoints of the values in the file, which are the endpoints of the segments
                pos = (pos.iloc[:,:-1]+pos.iloc[:,1:])/2

                newcols = pd.MultiIndex.from_product([[gid],pos.columns])
                pos.columns = newcols
                newPos = pd.concat((newPos,pos),axis=1)

    return newPos

def getReport(path_to_simconfig):

    '''
    Loads compartment report from simulation_config
    '''

    with open(path_to_simconfig) as f:

        simconfig = json.load(f)

        outputdir = simconfig['output']['output_dir']

        report = simconfig['reports']['compartment']['file_name']

        path_to_report = outputdir + '/' + report + '.h5'

    r = lb.ElementReportReader(path_to_report)
    population_name = r.get_population_names()[0]

    r = r[population_name]

    return r

def writeH5File(electrodeType,path_to_simconfig,segment_position_folder,outputfile,numFilesPerFolder,sigma=0.277,path_to_fields=None):

    '''
    path_to_simconfig refers to the BlueConfig from the 1-timestep simulation used to get the segment positions
    segment_position_folder refers to the path to the pickle file containing the potential at each segment. This is the output of the interpolation script
    '''

    r = getReport(path_to_simconfig)


    allNodeIds = r.get_node_ids()

    numNodeIds = len(allNodeIds)

    numPositionFiles = np.ceil(numNodeIds/1000) # Each position file has 1000 gids

    rank = MPI.COMM_WORLD.Get_rank()
    nranks = MPI.COMM_WORLD.Get_size()

    positions = load_positions(segment_position_folder,numFilesPerFolder, numPositionFiles, rank, nranks)

    iterationsPerFile = int(nranks/numPositionFiles) # How many ranks is any position file divided among
    iterationSize = int(1000/iterationsPerFile) # Number of node_ids processed on this rank

    iteration = int(rank/numPositionFiles)


    h5 = h5py.File(outputfile, 'a',driver='mpio',comm=MPI.COMM_WORLD)


    #### For the current rank, selects node ids for which to calculate the coefficients
    try:
        node_ids= np.unique(np.array(list(positions.columns))[:,0])[iteration*iterationSize:(iteration+1)*iterationSize]
    except:
        node_ids = np.unique(np.array(list(positions.columns))[:,0])[iteration*iterationSize:]

    if len(node_ids) == 0:
        h5.close()
        return 1

    #####

    node_ids_sonata = lb.Selection(values=node_ids)

    data_frame = r.get(node_ids=node_ids_sonata,tstart=0,tstop=0.1) # Loads compartment report for sleected node_ids
    data = pd.DataFrame(data_frame.data, columns=pd.MultiIndex.from_tuples(tuple(map(tuple,data_frame.ids)), names=['gid','section']), index=data_frame.times) # Writes compartment report as pandas dataframe


    columns = data.columns

    positions = positions[node_ids] # Gets positions for specific node ids

    coeffList = []

    for electrode in h5['electrodes'].keys():

        if electrode != population_name: # The field /electrodes/{population_name} contains the scaling factors, not the metadata

            epos = h5['electrodes'][electrode]['position'] # Gets position for each electrode

            if electrodeType == 'LFP':
                coeffs = get_coeffs_lfp(positions,columns,ePos,sigma)
            else:

                newPositions = getSegmentMidpts(positions,node_ids) # For EEG, we need the segment centers, not the endpoints
                coeffs = get_coeffs_eeg(newPositions,path_to_fields)

            coeffList.append(coeffs)


    for i, id in enumerate(node_ids):


        for j, l in enumerate(coeffList):

            coeffs = np.array(l.loc[:,id].values).T

            if j == 0:
                newCoeffs = coeffs
            else:
                newCoeffs = np.hstack((newCoeffs, coeffs))

        add_data(h5, gid, newCoeffs ,population_name)

    h5.close()

    return 0


if __name__=='__main__':


    type = sys.argv[1] # Either EEG or LFP

    path_to_simconfig = sys.argv[2] # simulation_config.json with one-timestep compartment report
    segment_position_folder = sys.argv[3] # Folder with segment positions; output of getPositions.py
    outputfile = sys.argv[4]

    numFilesPerFolder = int(sys.argv[5]) # Number of files per subfolder in segment positions folder

    electrode_csv = sys.argv[6] # Data about each electrode in array

    electrode_df = pd.read_csv(electrode_csv,header=0,index_col=0)

    numElectrodes = len(electrode_df.index)

    sigma = 0.277 # Conductance of the brain tissue, in S/m
    path_to_fields = None # H5 file generated by the finite element solver with the potential field resulting from a current between two recording electrodes

    if len(sys.argv)>7: # Specify either conductance or a potential field, not both

        try:
            sigma = float(sys.argv[7]) # If the argument is a number, assume it is a conductance
        except:
            path_to_fields = sys.argv[7]


    file = h5py.File(outputfile)

    names = []
    positions = []
    for i in range(numElectrodes):
        names.append(electrode_df.index[i])

        positions.append(file['electrodes'][str(i)]['position'][:]) # Take electrode positions from h5 coefficient file



    file.close()

    electrodePositions = np.array(positions)

    writeH5File(type,path_to_simconfig,segment_position_folder,outputfile,numFilesPerFolder,sigma,path_to_fields)
