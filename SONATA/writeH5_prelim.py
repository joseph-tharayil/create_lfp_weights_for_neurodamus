import numpy as np
import h5py
import os
import pandas as pd
import sys
import bluepysnap as bp
import json

class ElectrodeFileStructure(object):

    '''
    This class writes datasets to the h5 file
    '''

    def __init__(self, h5, lst_ids, electrodes, population_name, **kwargs):

        '''
        h5: h5 file returned by h5py.File(filename,'w')
        lst_ids: node ids
        electrodes: Dictionary with metadata about electrodes
        population_name: Sonata population
        **kwargs: currently expected to take the circuit path
        '''


        dset = h5.create_dataset(population_name+"/node_ids", data=sorted(lst_ids))

        for k, v in kwargs.items():
            dset.attrs.create(k, v)

        index = 0

        ### Iterates through electrode dictionary to write metadata
        for key, electrode in electrodes.items(): # Iterates through electrodes


            
            h5.create_dataset("electrodes/" + str(key) + '/'+population_name,data=index) # Index of the column corresponding to this electrode in /electrodes/{population_name}/scaling_factors
            index += 1

            for item in electrode.items(): # Iterates through metadata fields for each electrode
            
                h5.create_dataset("electrodes/" + str(key) + '/' + item[0],
                              data=item[1])
        ####

        self._ids = np.array(lst_ids)

    def file(self):
        return h5py.File(self._fn, "r+")

    def lengths(self, gid):
        assert gid in self._ids
        return "lengths/" + str(int(gid))

    def offsets(self,population_name):
        return population_name+"/offsets"

    def weights(self, population_name):

        return '/electrodes/'+population_name+'/scaling_factors'

def get_offsets(sectionIdsFrame):
    
    unique, counts = np.unique(sectionIdsFrame['id'].values,return_counts=True) # Unique node_ids and number of segments per node id

    out_offsets = np.hstack((np.array([0]),np.cumsum(counts))) # Offset from start of list for each node id
    
    return out_offsets

def write_all_neuron(sectionIdsFrame, population_name, h5, file, electrode_struc):
    
    file.create_dataset(h5.weights(population_name), data=np.ones([len(sectionIdsFrame['id'].values),len(electrode_struc.items())+1])) # Initializes /electrodes/{population_name}/scaling_factors with array of ones of size nSegments x (nElectrodes+1)

    out_offsets = get_offsets(sectionIdsFrame)

    file.create_dataset(h5.offsets(population_name), data=out_offsets) # The offset for each node in the scaling_factors field


def makeElectrodeDict(electrode_csv):

    '''
    Reads electrode metadata from input csv file and writes it to a dictionary
    '''

    electrode_df = pd.read_csv(electrode_csv,header=0,index_col=0)

    electrodes = {}

    for i in range(len(electrode_df.values)): # Iterates through each electrode in array

        name = electrode_df.index.values[i]

        position = np.array([electrode_df['x'].iloc[i],electrode_df['y'].iloc[i],electrode_df['z'].iloc[i]])

        if 'layer' in electrode_df.columns:

            layer = electrode_df['layer'].iloc[i]

        else:

            layer = "NA"

        if 'region' in electrode_df.columns:
            region = electrode_df['region'].iloc[i]
        else:
            region = 'NA'
            
        if 'type' in electrode_df.columns:
            electrodeType = electrode_df['type'].iloc[i]
        else:
            electrodeType = 'LineSource'

        electrodes[name] = {'position': position,'type': electrodeType,
        'region':region,'layer':layer}


    return electrodes

def getSimInfo(path_to_simconfig):

    '''
    Returns the following:
    circuit: Path to the circuit used to generate the time steps. Gets written to the h5 file and is checked by neurodamus when and LFP simulation is run. LFP simulation will fail if it uses a different circuit than the one in the h5 file
    population_name: SONATA population name
    node_ids: list of ids for which segment coefficients will be written
    data: dataframe with a compartment report, whose columns are the node_id and sectionId of each neuron
    '''

    with open(path_to_simconfig) as f:

        circuitpath = json.load(f)['network']

    r1 = bp.Simulation(path_to_simconfig)
    r = r1.reports[list(r1.reports.keys())[0]]

    population_name = r.population_names[0]

    report = r[population_name]
    nodeIds = report.node_ids

    data = report.get(group=nodeIds,t_start=0,t_stop=r.dt)
    data.columns = data.columns.rename('id',level=0)
    data.columns = data.columns.rename('section',level=1)

    return circuitpath, population_name, nodeIds, data


def writeH5File(path_to_simconfig,outputfile,electrode_csv):

    '''
    path_to_simconfig refers to the simulation_config from the 1-timestep simulation used to get the segment positions
    electrode_csv is a csv file containing the position, region, and layer of each electrode
    type is either EEG or LFP
    '''

    circuitpath, population_name, nodeIds, data = getSimInfo(path_to_simconfig)


    sectionIdsFrame = data.columns.to_frame()
    sectionIdsFrame.index = range(len(sectionIdsFrame))
    
    electrodes = makeElectrodeDict(electrode_csv) # Dictionary containing metadata about the electrodes

    h5file = h5py.File(outputfile,'w') # Creates h5 file for coefficients

    ### This block sets memory parameters that make writing the H5 file faster
    h5id = h5file.id
    cc = h5id.get_mdc_config()
    cc.max_size = 1024*1024*124
    h5id.set_mdc_config(cc)
    #####

    h5 = ElectrodeFileStructure(h5file, nodeIds, electrodes, population_name, circuit=circuitpath) # Initializes fields in h5 file


    write_all_neuron(sectionIdsFrame, population_name, h5, h5file, electrodes)  # For each node_id, initializes coefficient field in h5 file

    h5file.close()


if __name__=='__main__':

    '''
    path_to_simconfig refers to the simulation_config from the 1-timestep simulation used to get the segment positions
    electrode_csv is a csv file containing the position, region, and layer of each electrode
    type is either LineSource or Reciprocity
    '''

    electrode_csv = sys.argv[1]

    path_to_simconfig = sys.argv[2]

    outputfile = sys.argv[3]

    writeH5File(path_to_simconfig,outputfile,electrode_csv)
